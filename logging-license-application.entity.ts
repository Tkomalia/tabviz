import { ApiHideProperty } from '@nestjs/swagger';
import { CrudValidationGroups } from '@nestjsx/crud';
import { IsNotEmpty, IsOptional } from 'class-validator';
import { BaseEntity } from 'src/common/classes/BaseEntity.class';
import { Column, Entity, Generated, OneToMany, ManyToOne, PrimaryGeneratedColumn } from 'typeorm';
import { LoggingLicense } from './logging-license.entity';
import { LoggingLicenseDenial } from './logging-license-denial.entity';
import { CalculationField } from './calculation-field.entity';
import { ContractHandbook } from './contract-handbook.entity';
import { TechnologicalMap } from './technological-map.entity';
const { CREATE, UPDATE } = CrudValidationGroups;

/**
 * LoggingLicenseApplication
 */
@Entity()
export class LoggingLicenseApplication extends BaseEntity {
    @IsOptional({ groups: [CREATE] })
    @IsNotEmpty({ groups: [UPDATE] })
    @PrimaryGeneratedColumn()
    id: number;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @ManyToOne(() => ContractHandbook, (o) => o.logging_license_application, { cascade: true })
    contract_handbook: ContractHandbook;

    @ApiHideProperty()
    @OneToMany(() => LoggingLicense, (o) => o.logging_license_application)
    logging_license: LoggingLicense[];

    @ApiHideProperty()
    @OneToMany(() => LoggingLicenseDenial, (o) => o.logging_license_application)
    logging_license_denial: LoggingLicenseDenial[];

    @ApiHideProperty()
    @OneToMany(() => CalculationField, (o) => o.logging_license_application)
    calculation_field: CalculationField[];

    @ApiHideProperty()
    @OneToMany(() => TechnologicalMap, (o) => o.logging_license_application)
    technological_map: TechnologicalMap[];

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер заявления' })
    application_info_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'date', comment: 'Дата заявления' })
    application_info_creation_date?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Основные сведения ЮЛ, БИН' })
    basic_info_ul_bin?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Основные сведения ЮЛ, ФИО' })
    basic_info_ul_fio?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Основные сведения ЮЛ, Должность представителя' })
    basic_info_ul_work_position?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о юридическом лице, Полное наименование' })
    info_ul_full_name?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о юридическом лице, ОКПО' })
    info_ul_okpo?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о юридическом лице, ОКЭД' })
    info_ul_oked?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({
        type: 'text',
        comment: 'Данные о юридическом лице, Серия свидетельства о государственной регистрации',
    })
    info_ul_gov_reg_serial_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'date', comment: 'Данные о юридическом лице, Дата регистрации' })
    info_ul_reg_date?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о юридическом лице, Статус юридического лица' })
    info_ul_ul_status_code?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о физическом лице, ИИН' })
    info_fl_iin?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о физическом лице, Имя' })
    info_fl_surname?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о физическом лице, Фамилия' })
    info_fl_name?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Данные о физическом лице, Отчество' })
    info_fl_middle_name?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Сведения уд, Тип' })
    id_type?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Сведения уд, Номер' })
    id_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Сведения уд, Серия' })
    id_series?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Сведения уд, Дата выдачи' })
    id_data_of_issue?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'date', comment: 'Сведения уд, Дата окончания' })
    id_expiration_date?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Сведения уд, Орган выдачи' })
    id_issuing_authority?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Почтовый индекс' })
    postcode?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Страна, Область, Район, Населенный пункт' })
    locality?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Название улицы' })
    street?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер дома/здания' })
    house_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер дома/здания' })
    home_index?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер квартиры/офиса' })
    apartment_office_index?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер телефона' })
    phone_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Область, код' })
    region_code?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Учреждение (лесовладелец), код' })
    forest_owner?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Лесничество, код' })
    forestry_code?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Вид лесопользования, код' })
    forestry_type_code?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Подвид лесопользования, код' })
    forestry_subtype_code?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Тип договора' })
    contract_type_code?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер договора' })
    contract_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'date', comment: 'Дата договора' })
    contract_date?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Дополнительная информация по договору' })
    contract_add_info?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Номер приказа' })
    order_number?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'date', comment: 'Дата приказа' })
    order_date?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Дополнительная информация по приказу' })
    order_add_info?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'boolean', comment: 'Подтверждение достоверности информации' })
    is_reliable?: boolean;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'boolean', comment: 'Согласие на использование сведений' })
    is_agreed?: boolean;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'boolean', comment: 'Ознакомление с правилами' })
    is_familiarized?: boolean;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Заявитель' })
    applicant?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'date', comment: 'Дата' })
    date?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'ЭЦП' })
    ecp?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'text', comment: 'Статус' })
    status?: string;

    @IsOptional({ groups: [CREATE, UPDATE] })
    @Column({ type: 'boolean', comment: 'Просрочено ли' })
    is_overdue?: boolean;

    // @IsNotEmpty({ groups: [CREATE] })
    // @IsOptional({ groups: [UPDATE] })
    // @ManyToOne(() => Types, (o) => o.logging_license_application, { cascade: true })
    // type: Types;

    // @ApiHideProperty()
    // @OneToMany(() => Datas, (o) => o.logging_license_application)
    // datas: Datas[];
}
